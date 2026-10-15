package com.hekma.identity.repository;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.CustomRoleAuthorityEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Set;
import java.util.UUID;

@Repository
public interface CustomRoleAuthorityRepository extends JpaRepository<CustomRoleAuthorityEntity, UUID> {

    List<CustomRoleAuthorityEntity> findByCustomRoleId(UUID customRoleId);

    @Query("SELECT cra.authority FROM CustomRoleAuthorityEntity cra WHERE cra.customRole.id = :customRoleId")
    Set<Authority> findAuthoritiesByCustomRoleId(@Param("customRoleId") UUID customRoleId);

    void deleteByCustomRoleId(UUID customRoleId);
}
